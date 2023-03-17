from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from wtforms import Form, StringField, IntegerField, validators
from netaddr import *
import ipaddress
import flask_excel as excel

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///test.db"
db = SQLAlchemy(app)
excel.init_excel(app)


class IPAddressess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prefix = db.Column(db.Integer)
    subnet_address = db.Column(db.Integer)
    adress_range = db.Column(db.Integer)
    total_hosts = db.Column(db.Integer)
    useable_ip = db.Column(db.Integer)
    comment = db.Column(db.String)
    merge_check = db.Column(db.Integer)
    sorting = db.Column(db.String)
    counter = db.Column(db.Integer)

    def __repr__(self):
        return self.subnet_address


###For redeploying DB tables
def recreate():
    with app.app_context():
        db.drop_all()
        db.create_all()
        print("All tables redployed")


recreate()


# Validating IP
class ValidateIP(Form):
    inserted_ip = StringField(
        "inserted_ip",
        validators=[
            validators.IPAddress(
                ipv4=True, ipv6=False, message="Only IPv4 addresses are valid."
            )
        ],
    )

    inserted_prefix = IntegerField(
        "inserted_prefix",
        validators=[
            validators.NumberRange(min=2, max=32, message="Valid prefix range 2 - 32.")
        ],
    )


# Download function
@app.route("/download/", methods=["GET"])
def do_custom_export():
    query_sets = IPAddressess.query.all()
    column_names = [
        "subnet_address",
        "adress_range",
        "total_hosts",
        "useable_ip",
        "comment",
    ]
    return excel.make_response_from_query_sets(
        query_sets,
        column_names,
        "xlsx",
        dest_sheet_name="Results from Subnet Calculator",
    )


# Comment function
@app.route("/comment/<int:id>", methods=["POST", "GET"])
def comment(id):
    new_comment = IPAddressess.query.get_or_404(id)
    if request.method == "POST":
        new_comment.comment = request.form["comment"]
        try:
            db.session.commit()
            return redirect("/")
        except:
            return "There was an issue posting your comment"
    else:
        return redirect("/")


# Start function. Azure regulated IP-ranges
@app.route("/", methods=["POST", "GET"])
def submit():
    form = ValidateIP(request.form)
    if request.method == "POST":
        inserted_ip = request.form["inserted_ip"]
        inserted_prefix = request.form["inserted_prefix"]
        if form.validate():
            new_ip = inserted_ip + "/" + (str(inserted_prefix))
            prefix = int(inserted_prefix)
            prefix_minus = prefix - 1
            ip = IPNetwork(new_ip)
            ip_range = (
                (str(IPAddress(ip.first))) + " - " + (str(IPAddress(str(ip.last))))
            )
            hosts = str(ip.size - 5)
            useable_IP = (
                (str(IPAddress(ip.first + 3)))
                + " - "
                + (str(IPAddress(str(ip.last - 2))))
            )
            # Convert IP to int for sorting
            ip_int = int(ipaddress.IPv4Address(inserted_ip))

            total_ip = IPAddressess(
                sorting=ip_int,
                prefix=prefix_minus,
                subnet_address=new_ip,
                adress_range=ip_range,
                total_hosts=hosts,
                useable_ip=useable_IP,
            )

            try:
                db.session.add(total_ip)
                db.session.commit()
                return redirect("/")
            except:
                return "Failed to submit. Try again."
        else:
            return "Input is not a valid IPv4 address."

    else:
        check_if_merge_available()
        showIP = IPAddressess.query.order_by(IPAddressess.sorting).all()
        return render_template("index.html", showIP=showIP)


def check_if_merge_available():
    rowspan = db.session.query(IPAddressess.merge_check).all()
    for row in rowspan:
        counter = rowspan.count(row)
        if counter == 1:
            to_int = [str(x) for x in row]
            finish = to_int[0]
            db.session.query(IPAddressess).filter(
                IPAddressess.merge_check == finish
            ).update({"counter": "2"})
            db.session.commit()
        else:
            to_int = [str(x) for x in row]
            finish = to_int[0]
            db.session.query(IPAddressess).filter(
                IPAddressess.merge_check == finish
            ).update({"counter": "1"})
            db.session.commit()
    return redirect("/")


@app.route("/delete/")
def delete_all_current_data():
    get_all_records = IPAddressess.query.all()
    for num in get_all_records:
        db.session.delete(num)
    db.session.commit()
    return redirect("/")


def delete_single_record(id):
    get_id_to_delete = IPAddressess.query.get_or_404(id)
    try:
        db.session.delete(get_id_to_delete)
        db.session.commit()
    except:
        return "There was an error deleting"

    return redirect("/")


@app.route("/merge/<int:id>")
def merge(id):
    get_id_for_merge = IPAddressess.query.get_or_404(id)
    check_for_merge = get_id_for_merge.merge_check
    check_for_hosts = get_id_for_merge.total_hosts

    merge_list = []
    matching = (
        db.session.query(IPAddressess)
        .filter_by(merge_check=check_for_merge, total_hosts=check_for_hosts)
        .all()
    )

    subnet_one = str(matching[0])
    try:
        subnet_two = str(matching[1])
    except:
        return redirect("/")

    merge_list.append(subnet_one)
    merge_list.append(subnet_two)
    merged_subnet = cidr_merge(merge_list)
    # Merges the two subnets
    add_subnet(merged_subnet[0])

    # Deletes the two subnets after merging
    delete_first_subnet = IPAddressess.query.filter_by(
        subnet_address=subnet_one
    ).first()
    delete_first_id = delete_first_subnet.id
    delete_second_subnet = IPAddressess.query.filter_by(
        subnet_address=subnet_two
    ).first()
    delete_second_id = delete_second_subnet.id

    delete_single_record(delete_first_id)
    delete_single_record(delete_second_id)

    return redirect("/")


@app.route("/divide/<int:id>")
def divide(id):
    get_ip = IPAddressess.query.get_or_404(id)
    to_string = str(get_ip)
    ip_convert = IPNetwork(str(get_ip))
    ip_split = to_string.split("/")
    prefix = int(ip_split[1])
    both_subnets = list(ip_convert.subnet(prefix + 1))

    subnets(both_subnets, id, prefix)

    return redirect("/")


# Adding merged subnet
def add_subnet(ip):
    ip_int = int(ipaddress.IPv4Address(ip[-3]))

    new_ip = str(IPNetwork(ip))
    prefix_to_int = int(new_ip[-2:])

    final_prefix = prefix_to_int - 1

    new_range = (str(IPAddress(ip.first))) + " - " + (str(IPAddress(str(ip.last))))
    new_host = str(ip.size - 5)
    new_useable_ip = (
        (str(IPAddress(ip.first + 3))) + " - " + (str(IPAddress(str(ip.last - 2))))
    )

    matching = IPAddressess.query.filter_by(total_hosts=new_host).first()
    try:
        match_merge_check = matching.merge_check
    except:
        match_merge_check = "1"

    new_merge_id = str(match_merge_check)
    new_merged = IPAddressess(
        sorting=ip_int,
        prefix=final_prefix,
        subnet_address=new_ip,
        adress_range=new_range,
        total_hosts=new_host,
        useable_ip=new_useable_ip,
        merge_check=new_merge_id,
    )

    db.session.add(new_merged)
    db.session.commit()


def subnets(ip_merged, id, prefix):
    subnet_one = IPNetwork(str(ip_merged[0]))
    subnet_one_to_string = str(subnet_one)
    subnet_one_list = list(subnet_one)
    hosts_one = subnet_one.size - 5
    subnet_one_range = (str(subnet_one_list[0])) + " - " + (str(subnet_one_list[-1]))
    subnet_one_useable = (str(subnet_one_list[3])) + " - " + (str(subnet_one_list[-3]))
    sorting_one = int(ipaddress.IPv4Address(subnet_one[-3]))

    subnet_one_total = IPAddressess(
        sorting=sorting_one,
        prefix=prefix,
        subnet_address=subnet_one_to_string,
        adress_range=subnet_one_range,
        total_hosts=hosts_one,
        useable_ip=subnet_one_useable,
        merge_check=id,
    )

    subnet_two = IPNetwork(str(ip_merged[1]))
    subnet_two_to_string = str(subnet_two)
    subnet_two_list = list(subnet_two)
    hosts_two = subnet_two.size - 5
    subnet_two_range = (str(subnet_two_list[0])) + " - " + (str(subnet_two_list[-1]))
    subnet_two_useable = (str(subnet_two_list[3])) + " - " + (str(subnet_two_list[-3]))
    sorting_two = int(ipaddress.IPv4Address(subnet_two[-3]))

    subnet_two_total = IPAddressess(
        sorting=sorting_two,
        prefix=prefix,
        subnet_address=subnet_two_to_string,
        adress_range=subnet_two_range,
        total_hosts=hosts_two,
        useable_ip=subnet_two_useable,
        merge_check=id,
    )
    db.session.add(subnet_two_total)
    db.session.add(subnet_one_total)
    db.session.commit()
    delete_single_record(id)

    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)
